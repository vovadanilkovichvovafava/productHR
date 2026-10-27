import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import EmptyState, {
  EmptyCandidates,
  EmptyVacancies,
  EmptySearch,
  EmptyKanban,
  EmptyAnalysis,
  EmptyFiles,
  EmptyChats,
  EmptyCalls,
  EmptyHistory,
  EmptyEntityVacancies,
  EmptyError,
  EmptyRecommendations
} from '../EmptyState';
import { Briefcase } from 'lucide-react';

// Wrapper component for router-dependent tests
const RouterWrapper = ({ children }: { children: React.ReactNode }) => (
  <BrowserRouter>{children}</BrowserRouter>
);

describe('EmptyState', () => {
  describe('Base EmptyState component', () => {
    it('should render title and description', () => {
      render(
        <RouterWrapper>
          <EmptyState
            title="Test Title"
            description="Test Description"
            animated={false}
          />
        </RouterWrapper>
      );

      expect(screen.getByText('Test Title')).toBeInTheDocument();
      expect(screen.getByText('Test Description')).toBeInTheDocument();
    });

    it('should render with custom icon', () => {
      render(
        <RouterWrapper>
          <EmptyState
            icon={Briefcase}
            title="With Icon"
            animated={false}
          />
        </RouterWrapper>
      );

      expect(screen.getByText('With Icon')).toBeInTheDocument();
    });

    it('should render a single action button from actions prop', () => {
      const onClick = vi.fn();
      render(
        <RouterWrapper>
          <EmptyState
            title="Test"
            actions={[{ label: 'Click Me', onClick }]}
            animated={false}
          />
        </RouterWrapper>
      );

      const button = screen.getByRole('button', { name: /click me/i });
      expect(button).toBeInTheDocument();

      fireEvent.click(button);
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('should render multiple action buttons when actions prop is provided', () => {
      const onClick1 = vi.fn();
      const onClick2 = vi.fn();
      render(
        <RouterWrapper>
          <EmptyState
            title="Test"
            actions={[
              { label: 'Primary Action', onClick: onClick1, variant: 'primary' },
              { label: 'Secondary Action', onClick: onClick2, variant: 'secondary' }
            ]}
            animated={false}
          />
        </RouterWrapper>
      );

      expect(screen.getByRole('button', { name: /primary action/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /secondary action/i })).toBeInTheDocument();
    });

    it('should render link when link prop is provided', () => {
      render(
        <RouterWrapper>
          <EmptyState
            title="Test"
            link={{ label: 'Go to Page', to: '/page' }}
            animated={false}
          />
        </RouterWrapper>
      );

      const link = screen.getByRole('link', { name: /go to page/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', '/page');
    });

    it('should render tips when tips prop is provided', () => {
      render(
        <RouterWrapper>
          <EmptyState
            title="Test"
            tips={['Tip 1', 'Tip 2', 'Tip 3']}
            animated={false}
          />
        </RouterWrapper>
      );

      expect(screen.getByText('Tip 1')).toBeInTheDocument();
      expect(screen.getByText('Tip 2')).toBeInTheDocument();
      expect(screen.getByText('Tip 3')).toBeInTheDocument();
    });

    it('should apply different size styles', () => {
      const { rerender } = render(
        <RouterWrapper>
          <EmptyState title="Small" size="sm" animated={false} />
        </RouterWrapper>
      );
      expect(screen.getByText('Small')).toBeInTheDocument();

      rerender(
        <RouterWrapper>
          <EmptyState title="Medium" size="md" animated={false} />
        </RouterWrapper>
      );
      expect(screen.getByText('Medium')).toBeInTheDocument();

      rerender(
        <RouterWrapper>
          <EmptyState title="Large" size="lg" animated={false} />
        </RouterWrapper>
      );
      expect(screen.getByText('Large')).toBeInTheDocument();
    });

    it('should apply variant styles', () => {
      const { rerender } = render(
        <RouterWrapper>
          <EmptyState title="Primary" variant="primary" animated={false} />
        </RouterWrapper>
      );
      expect(screen.getByText('Primary')).toBeInTheDocument();

      rerender(
        <RouterWrapper>
          <EmptyState title="Search" variant="search" animated={false} />
        </RouterWrapper>
      );
      expect(screen.getByText('Search')).toBeInTheDocument();

      rerender(
        <RouterWrapper>
          <EmptyState title="Filter" variant="filter" animated={false} />
        </RouterWrapper>
      );
      expect(screen.getByText('Filter')).toBeInTheDocument();

      rerender(
        <RouterWrapper>
          <EmptyState title="Error" variant="error" animated={false} />
        </RouterWrapper>
      );
      expect(screen.getByText('Error')).toBeInTheDocument();
    });
  });

  describe('EmptyCandidates', () => {
    it('should render primary variant with action buttons', () => {
      const onUploadResume = vi.fn();
      const onCreateCandidate = vi.fn();

      render(
        <RouterWrapper>
          <EmptyCandidates
            onUploadResume={onUploadResume}
            onCreateCandidate={onCreateCandidate}
          />
        </RouterWrapper>
      );

      expect(screen.getByText('Пока нет кандидатов')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /загрузить резюме/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /создать кандидата/i })).toBeInTheDocument();
    });

    it('should render search variant with query', () => {
      render(
        <RouterWrapper>
          <EmptyCandidates variant="search" query="John Doe" />
        </RouterWrapper>
      );

      expect(screen.getByText('Ничего не найдено')).toBeInTheDocument();
      expect(screen.getByText(/По запросу "John Doe"/)).toBeInTheDocument();
    });

    it('should render filter variant', () => {
      render(
        <RouterWrapper>
          <EmptyCandidates variant="filter" />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет подходящих кандидатов')).toBeInTheDocument();
    });
  });

  describe('EmptyVacancies', () => {
    it('should render primary variant with create button', () => {
      const onCreate = vi.fn();

      render(
        <RouterWrapper>
          <EmptyVacancies onCreate={onCreate} />
        </RouterWrapper>
      );

      expect(screen.getByText('Пока нет вакансий')).toBeInTheDocument();

      const button = screen.getByRole('button', { name: /создать вакансию/i });
      fireEvent.click(button);
      expect(onCreate).toHaveBeenCalledTimes(1);
    });

    it('should render search variant with query', () => {
      render(
        <RouterWrapper>
          <EmptyVacancies variant="search" query="Frontend Developer" />
        </RouterWrapper>
      );

      expect(screen.getByText('Вакансии не найдены')).toBeInTheDocument();
      expect(screen.getByText(/По запросу "Frontend Developer"/)).toBeInTheDocument();
    });

    it('should render filter variant', () => {
      render(
        <RouterWrapper>
          <EmptyVacancies variant="filter" />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет подходящих вакансий')).toBeInTheDocument();
    });
  });

  describe('EmptySearch', () => {
    it('should render with query and tips', () => {
      render(
        <RouterWrapper>
          <EmptySearch query="test query" entity="candidates" />
        </RouterWrapper>
      );

      expect(screen.getByText('Ничего не найдено')).toBeInTheDocument();
      expect(screen.getByText(/По запросу "test query"/)).toBeInTheDocument();
      expect(screen.getByText('Проверьте правильность написания')).toBeInTheDocument();
    });

    it('should render clear button when onClear is provided', () => {
      const onClear = vi.fn();
      render(
        <RouterWrapper>
          <EmptySearch query="test" onClear={onClear} />
        </RouterWrapper>
      );

      const button = screen.getByRole('button', { name: /сбросить поиск/i });
      fireEvent.click(button);
      expect(onClear).toHaveBeenCalledTimes(1);
    });
  });

  describe('EmptyKanban', () => {
    it('should render with action buttons', () => {
      const onAddFromBase = vi.fn();
      const onUploadResume = vi.fn();

      render(
        <RouterWrapper>
          <EmptyKanban
            onAddFromBase={onAddFromBase}
            onUploadResume={onUploadResume}
          />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет откликов на вакансию')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /добавить из базы/i }));
      expect(onAddFromBase).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByRole('button', { name: /загрузить резюме/i }));
      expect(onUploadResume).toHaveBeenCalledTimes(1);
    });
  });

  describe('EmptyAnalysis', () => {
    it('should render with analysis button', () => {
      const onRunAnalysis = vi.fn();

      render(
        <RouterWrapper>
          <EmptyAnalysis onRunAnalysis={onRunAnalysis} />
        </RouterWrapper>
      );

      expect(screen.getByText('AI-анализ не проводился')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /запустить анализ/i }));
      expect(onRunAnalysis).toHaveBeenCalledTimes(1);
    });

    it('should show loading state when isLoading is true', () => {
      render(
        <RouterWrapper>
          <EmptyAnalysis onRunAnalysis={() => {}} isLoading={true} />
        </RouterWrapper>
      );

      expect(screen.getByRole('button', { name: /анализ/i })).toBeInTheDocument();
    });
  });

  describe('EmptyFiles', () => {
    it('should render with upload button', () => {
      const onUpload = vi.fn();

      render(
        <RouterWrapper>
          <EmptyFiles onUpload={onUpload} />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет прикреплённых файлов')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /загрузить файл/i }));
      expect(onUpload).toHaveBeenCalledTimes(1);
    });
  });

  describe('EmptyChats', () => {
    it('should render with link button', () => {
      const onLink = vi.fn();

      render(
        <RouterWrapper>
          <EmptyChats onLink={onLink} />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет связанных чатов')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /привязать чат/i }));
      expect(onLink).toHaveBeenCalledTimes(1);
    });
  });

  describe('EmptyCalls', () => {
    it('should render with link button', () => {
      const onLink = vi.fn();

      render(
        <RouterWrapper>
          <EmptyCalls onLink={onLink} />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет записей звонков')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /привязать звонок/i }));
      expect(onLink).toHaveBeenCalledTimes(1);
    });
  });

  describe('EmptyHistory', () => {
    it('should render correctly', () => {
      render(
        <RouterWrapper>
          <EmptyHistory />
        </RouterWrapper>
      );

      expect(screen.getByText('История пуста')).toBeInTheDocument();
    });
  });

  describe('EmptyEntityVacancies', () => {
    it('should render with add button', () => {
      const onAdd = vi.fn();

      render(
        <RouterWrapper>
          <EmptyEntityVacancies onAdd={onAdd} />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет откликов на вакансии')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /добавить в вакансию/i }));
      expect(onAdd).toHaveBeenCalledTimes(1);
    });
  });

  describe('EmptyError', () => {
    it('should render with retry button', () => {
      const onRetry = vi.fn();

      render(
        <RouterWrapper>
          <EmptyError message="Something went wrong" onRetry={onRetry} />
        </RouterWrapper>
      );

      expect(screen.getByText('Произошла ошибка')).toBeInTheDocument();
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /повторить/i }));
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('should render default message when message is not provided', () => {
      render(
        <RouterWrapper>
          <EmptyError />
        </RouterWrapper>
      );

      expect(screen.getByText('Не удалось загрузить данные. Попробуйте ещё раз.')).toBeInTheDocument();
    });
  });

  describe('EmptyRecommendations', () => {
    it('should render for candidate type', () => {
      render(
        <RouterWrapper>
          <EmptyRecommendations entityType="candidate" />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет рекомендаций')).toBeInTheDocument();
      expect(screen.getByText('Для этого кандидата пока нет подходящих вакансий')).toBeInTheDocument();
    });

    it('should render for vacancy type', () => {
      render(
        <RouterWrapper>
          <EmptyRecommendations entityType="vacancy" />
        </RouterWrapper>
      );

      expect(screen.getByText('Нет подходящих кандидатов')).toBeInTheDocument();
      expect(screen.getByText('Для этой вакансии пока нет подходящих кандидатов')).toBeInTheDocument();
    });
  });

});
